/** @typedef {{id:number,code:string,name:string,campus:string,group:'control'|'intervention',score:number|null,absent:boolean}} Student */
/** @typedef {{id:number,title:string,campus:string,exclude_absent:boolean,description:string,target_control:number,target_intervention:number}} Plan */
/** @typedef {{id:number,plan_id:number,status:string,source:'campus'|'roster',result:object|null,conclusion:string,published:boolean}} Report */
/** @typedef {{id:number,kind:'initial'|'supplementary',status:'pending'|'locked',idempotency_key:string,summary:object,counts:object}} RecruitBatch */
/** @typedef {{id:number,batch_id:number,group:'control'|'intervention',status:'pending'|'locked'|'withdrawn',student:object}} Assignment */
export const contractVersion=2;
